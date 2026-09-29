# Authentik integration

Bliss Secure MFA will use a separate identity plane for portal administrators and customer administrators.

## Why separate portal identity from multiOTP

The management portal must remain reachable even if the MFA engine itself is unhealthy. Using multiOTP as the only login path for the tool that repairs multiOTP creates an avoidable recovery dependency.

## Planned production flow

```text
Browser
  |
  v
Authentik
  |
  | OIDC access token
  v
mfa.blissitek.ca
  |
  v
Bliss Management API
  |
  +-- verify issuer
  +-- verify audience
  +-- verify signature from JWKS
  +-- verify token lifetime
  +-- read groups / subject
  |
  v
RBAC + tenant authorization
```

## Authentik groups

Create these groups:

- `bliss-mfa-super-admin`
- `bliss-mfa-technician`
- `bliss-mfa-billing`

Customer access is stored in the Bliss database through `PortalUser` and
`OrganizationMembership`; customer tenant authorization must not be granted
solely by a client-supplied organization identifier.

## API environment variables

```text
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
OIDC_GROUPS_CLAIM=groups
OIDC_STAFF_ADMIN_GROUP=bliss-mfa-super-admin
OIDC_STAFF_TECHNICIAN_GROUP=bliss-mfa-technician
OIDC_STAFF_BILLING_GROUP=bliss-mfa-billing
```

## Bootstrap authentication

`BLISS_BOOTSTRAP_API_KEY` is development-only.

The API explicitly refuses bootstrap-key authentication when
`APP_ENV=production`.

## Recommended Authentik application

Create one OIDC/OAuth2 provider and application for:

`mfa.blissitek.ca`

Use authorization code flow with PKCE for browser login. Require MFA for Bliss
staff accounts inside Authentik.

Exact client ID, redirect URLs and secrets are deployment values and are not
stored in Git.
