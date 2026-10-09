# Local dashboard appearance

The local portal follows the supplied multiOTP Web Console layout: indigo top
navigation, a centered account table, an expandable disabled/revoked section,
enrollment actions and recent events. Dashboard and RDP Users share the same
account-management component. Get started, administrators, audit and licensing
remain available. The reference executable was inspected for templates/styles,
not installed or executed.

This is an adaptation to the existing Bliss API. The **Windows Accounts** page
lists local Windows accounts (username, full name, enabled/disabled) matched to
MFA records: "MFA enrolled" (authenticator verified), "Enrollment pending",
"Not enrolled" or "Disabled account". "MFA enrolled" does not mean Windows
sign-in is protected; that is the separate RDP protection step. Domain accounts
are not discovered. **Enroll MFA** creates the MFA record with the exact Windows
account name and opens the existing QR enrollment flow. The appliance API checks
every new MFA username (including names typed on RDP Users) against enabled
local accounts, refuses case-insensitive duplicates and enforces the plan seat
limit. The page does not create Windows accounts, enable RDP enforcement, or
expose the reference executable's credential-provider settings. Existing account lifecycle endpoints remain in use, with inline
confirmation and enrollment forms.

Build with the project's Next.js dependencies (`npm install`, `npm run build`).
For a standalone installation, package `.next/standalone` and copy `.next/static`
to its `.next/static` directory. Include this portal build in the appliance
installer or a tested signed application update. Updating WordPress or the
licensing Docker backend alone does not replace a client's installed dashboard.

Validation: production compilation/TypeScript and standalone startup passed.
Browser checks used isolated demo accounts, inspected desktop/mobile layouts,
opened the new-user form and verified recent-event rendering. They do not prove
actual Windows RDP sign-in or constitute an installed-client upgrade test.
